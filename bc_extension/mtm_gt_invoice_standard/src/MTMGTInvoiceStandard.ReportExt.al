reportextension 71100 "MTM GT Invoice Standard" extends FacturaGTM
{
    dataset
    {
        add(SalesInvoiceHeader)
        {
            column(MTM_FEL_QR_Code; MTMFELQRCodeBase64)
            {
            }
            column(MTM_ISR_Comment; MTMISRComment)
            {
            }
            column(MTM_PO_Number; GetSalesInvoicePONumber(SalesInvoiceHeader))
            {
            }
            column(MTM_Booking_Label; GetSalesInvoiceBookingLabel(SalesInvoiceHeader))
            {
            }
            column(MTM_Booking; GetSalesInvoiceBooking(SalesInvoiceHeader))
            {
            }
            column(MTM_Containers_Label; GetSalesInvoiceContainersLabel(SalesInvoiceHeader))
            {
            }
            column(MTM_Containers; GetSalesInvoiceContainers(SalesInvoiceHeader))
            {
            }
            column(MTM_Invoice_Date_Text; FormatInvoiceDate(SalesInvoiceHeader."Posting Date"))
            {
            }
        }

        modify(SalesInvoiceHeader)
        {
            trigger OnAfterAfterGetRecord()
            begin
                Clear(MTMVisibleLineNo);
                Clear(MTMLinePageNo);
                Clear(MTMLineIndexOnPage);
                MTMFELQRCodeBase64 := BuildFELQRCodeBase64(GetFELUUID(SalesInvoiceHeader));
                MTMISRComment := BuildISRComment(SalesInvoiceHeader);
            end;
        }

        modify(SalesInvoiceLine)
        {
            trigger OnAfterAfterGetRecord()
            begin
                if IsMTMShipmentMetadataLine(GetSalesInvoiceLineInvoiceDescription(SalesInvoiceLine)) then begin
                    CurrReport.Skip();
                    exit;
                end;

                MTMVisibleLineNo += 1;
                MTMLinePageNo := ((MTMVisibleLineNo - 1) div 8) + 1;
                MTMLineIndexOnPage := ((MTMVisibleLineNo - 1) mod 8) + 1;
            end;
        }

        add(SalesInvoiceLine)
        {
            column(MTM_Line_Description; GetSalesInvoiceLineInvoiceDescription(SalesInvoiceLine))
            {
            }
            column(MTM_Line_Page_No; MTMLinePageNo)
            {
            }
            column(MTM_Line_Index_On_Page; MTMLineIndexOnPage)
            {
            }
        }
    }

    rendering
    {
        layout(MTMGTInvoiceStandard202606OnePage)
        {
            Type = RDLC;
            LayoutFile = './layouts/MTMGTInvoiceStandard202605.rdl';
            Caption = 'MTM GT Invoice Standard 2026-06 One Page';
            Summary = 'Approved MTM Guatemala invoice layout for print, PDF, and email attachment output.';
        }
    }

    var
        MTMFELQRCodeBase64: Text;
        MTMISRComment: Text;
        MTMVisibleLineNo: Integer;
        MTMLinePageNo: Integer;
        MTMLineIndexOnPage: Integer;
        NATISRCommentLbl: Label 'SUJETO A PAGOS TRIMESTRALES ISR', Locked = true;
        INTISRCommentLbl: Label 'SUJETO A PAGOS TRIMESTRALES ISR. SERVICIOS NO AFECTOS. NO AFECTO AL IVA (FUERA DEL HECHO GENERADOR ART. 3, 7 Y 8, LEY DEL IVA).', Locked = true;

    local procedure BuildISRComment(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    var
        SalesInvoiceLine: Record "Sales Invoice Line";
        LineNoPrefix: Text;
        HasNATLines: Boolean;
    begin
        SalesInvoiceLine.SetRange("Document No.", SalesInvoiceHeader."No.");

        if not SalesInvoiceLine.FindSet() then
            exit('');

        repeat
            LineNoPrefix := CopyStr(UpperCase(Format(SalesInvoiceLine."No.")), 1, 3);
            if LineNoPrefix = 'INT' then
                exit(INTISRCommentLbl);
            if LineNoPrefix = 'NAT' then
                HasNATLines := true;
        until SalesInvoiceLine.Next() = 0;

        if HasNATLines then
            exit(NATISRCommentLbl);

        exit('');
    end;

    local procedure GetFELUUID(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    var
        SalesInvoiceHeaderRef: RecordRef;
        SalesInvoiceHeaderFieldRef: FieldRef;
        FieldIndex: Integer;
    begin
        SalesInvoiceHeaderRef.GetTable(SalesInvoiceHeader);
        for FieldIndex := 1 to SalesInvoiceHeaderRef.FieldCount() do begin
            SalesInvoiceHeaderFieldRef := SalesInvoiceHeaderRef.FieldIndex(FieldIndex);
            if (SalesInvoiceHeaderFieldRef.Name() = 'Fiscal Invoice Number PAC') or
               (SalesInvoiceHeaderFieldRef.Caption() = 'Fiscal Invoice Number PAC')
            then
                exit(Format(SalesInvoiceHeaderFieldRef.Value()));
        end;

        exit('');
    end;

    local procedure GetSalesInvoiceLineInvoiceDescription(SalesInvoiceLine: Record "Sales Invoice Line"): Text
    var
        SalesInvoiceLineRef: RecordRef;
        FieldValue: Text;
        AccountDescription: Text;
    begin
        SalesInvoiceLineRef.GetTable(SalesInvoiceLine);
        FieldValue := GetCustomInvoiceDescription(SalesInvoiceLineRef);
        if FieldValue <> '' then
            exit(FieldValue);

        if SalesInvoiceLine.Description <> '' then
            exit(SalesInvoiceLine.Description);

        AccountDescription := GetTrackedAccountDescription(SalesInvoiceLine."No.");
        if AccountDescription <> '' then
            exit(AccountDescription);

        exit(SalesInvoiceLine.Description);
    end;

    local procedure GetCustomInvoiceDescription(RecordRef: RecordRef): Text
    var
        FieldRef: FieldRef;
        FieldIndex: Integer;
        FieldValue: Text;
    begin
        for FieldIndex := 1 to RecordRef.FieldCount() do begin
            FieldRef := RecordRef.FieldIndex(FieldIndex);
            if (FieldRef.Name() = 'Descripción Factura') or
               (FieldRef.Caption() = 'Descripción Factura') or
               (FieldRef.Name() = 'Description XL') or
               (FieldRef.Caption() = 'Description XL')
            then begin
                FieldValue := DelChr(Format(FieldRef.Value()), '<>', ' ');
                if FieldValue <> '' then
                    exit(FieldValue);
            end;
        end;

        exit('');
    end;

    local procedure GetTrackedAccountDescription(AccountNo: Code[20]): Text
    var
        Item: Record Item;
        GLAccount: Record "G/L Account";
        AccountPrefix: Text;
    begin
        AccountPrefix := CopyStr(UpperCase(Format(AccountNo)), 1, 3);
        if not (AccountPrefix in ['INT', 'NAT']) then
            exit('');

        if Item.Get(AccountNo) then
            if Item.Description <> '' then
                exit(UpperCase(Item.Description));

        if GLAccount.Get(AccountNo) then
            exit(UpperCase(GLAccount.Name));

        exit('');
    end;

    local procedure GetSalesInvoicePONumber(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    begin
        if SalesInvoiceHeader."Your Reference" <> '' then
            exit(SalesInvoiceHeader."Your Reference");

        if SalesInvoiceHeader."External Document No." <> '' then
            exit(SalesInvoiceHeader."External Document No.");

        exit(SalesInvoiceHeader."Order No.");
    end;

    local procedure FormatInvoiceDate(InvoiceDate: Date): Text
    begin
        if InvoiceDate = 0D then
            exit('');

        exit(Format(InvoiceDate, 0, '<Day,2>/<Month,2>/<Year4>'));
    end;

    local procedure GetSalesInvoiceBooking(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    var
        BookingValue: Text;
    begin
        if IsSalesInvoiceAirShipment(SalesInvoiceHeader) then
            exit(GetSalesInvoiceAirwayBill(SalesInvoiceHeader));

        BookingValue := GetPostedLineMarkerValue(SalesInvoiceHeader."No.", 'BOOKING NO.', 'CONTAINER');
        if BookingValue <> '' then
            exit(BookingValue);

        exit(GetPostedLineMarkerValue(SalesInvoiceHeader."No.", 'BOOKING', 'CONTAINER'));
    end;

    local procedure GetSalesInvoiceBookingLabel(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    begin
        if IsSalesInvoiceAirShipment(SalesInvoiceHeader) then
            exit('AWB:');

        exit('BOOKING:');
    end;

    local procedure GetSalesInvoiceContainers(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    var
        ContainerValue: Text;
    begin
        if IsSalesInvoiceAirShipment(SalesInvoiceHeader) then
            exit('');

        ContainerValue := GetPostedLineMarkerValues(SalesInvoiceHeader."No.", 'CONTAINER NUMBER');
        if ContainerValue <> '' then
            exit(ContainerValue);

        ContainerValue := GetPostedLineMarkerValues(SalesInvoiceHeader."No.", 'CONTAINERS');
        if ContainerValue <> '' then
            exit(ContainerValue);

        exit(GetPostedLineMarkerValues(SalesInvoiceHeader."No.", 'CONTAINER'));
    end;

    local procedure GetSalesInvoiceContainersLabel(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    begin
        if IsSalesInvoiceAirShipment(SalesInvoiceHeader) then
            exit('');

        exit('CONTENEDORES:');
    end;

    local procedure IsSalesInvoiceAirShipment(SalesInvoiceHeader: Record "Sales Invoice Header"): Boolean
    var
        ProductValue: Text;
    begin
        ProductValue := UpperCase(GetPostedLineMarkerValue(SalesInvoiceHeader."No.", 'PRODUCT', ''));
        exit((ProductValue = 'AIR') or (ProductValue = 'AEREO'));
    end;

    local procedure GetSalesInvoiceAirwayBill(SalesInvoiceHeader: Record "Sales Invoice Header"): Text
    var
        AirwayBillValue: Text;
    begin
        AirwayBillValue := GetPostedLineMarkerValue(SalesInvoiceHeader."No.", 'AWB', '');
        if AirwayBillValue <> '' then
            exit(AirwayBillValue);

        exit(GetPostedLineMarkerValue(SalesInvoiceHeader."No.", 'AIRWAY BILL', ''));
    end;

    local procedure GetPostedLineMarkerValues(DocumentNo: Code[20]; Marker: Text): Text
    var
        SalesInvoiceLine: Record "Sales Invoice Line";
        MarkerValue: Text;
        CombinedValue: Text;
    begin
        SalesInvoiceLine.SetRange("Document No.", DocumentNo);
        if not SalesInvoiceLine.FindSet() then
            exit('');

        repeat
            MarkerValue := ExtractMarkerValue(GetSalesInvoiceLineInvoiceDescription(SalesInvoiceLine), Marker, '');
            if MarkerValue <> '' then begin
                if CombinedValue <> '' then
                    CombinedValue := CombinedValue + ', ';
                CombinedValue := CopyStr(CombinedValue + MarkerValue, 1, 250);
            end;
        until SalesInvoiceLine.Next() = 0;

        exit(CombinedValue);
    end;

    local procedure GetPostedLineMarkerValue(DocumentNo: Code[20]; Marker: Text; NextMarker: Text): Text
    var
        SalesInvoiceLine: Record "Sales Invoice Line";
        MarkerValue: Text;
    begin
        SalesInvoiceLine.SetRange("Document No.", DocumentNo);
        if not SalesInvoiceLine.FindSet() then
            exit('');

        repeat
            MarkerValue := ExtractMarkerValue(GetSalesInvoiceLineInvoiceDescription(SalesInvoiceLine), Marker, NextMarker);
            if MarkerValue <> '' then
                exit(CopyStr(MarkerValue, 1, 250));
        until SalesInvoiceLine.Next() = 0;

        exit('');
    end;

    local procedure IsMTMShipmentMetadataLine(LineDescription: Text): Boolean
    begin
        exit(CopyStr(UpperCase(LineDescription), 1, 8) = 'MTM META');
    end;

    local procedure ExtractMarkerValue(SourceText: Text; Marker: Text; NextMarker: Text): Text
    var
        UpperSourceText: Text;
        UpperValueText: Text;
        ValueText: Text;
        MarkerPosition: Integer;
        StopPosition: Integer;
    begin
        UpperSourceText := UpperCase(SourceText);
        MarkerPosition := StrPos(UpperSourceText, Marker);
        if MarkerPosition = 0 then
            exit('');

        ValueText := CopyStr(SourceText, MarkerPosition + StrLen(Marker));
        ValueText := DelChr(ValueText, '<>', ' :#.-');

        if NextMarker <> '' then begin
            UpperValueText := UpperCase(ValueText);
            StopPosition := StrPos(UpperValueText, NextMarker);
            if StopPosition > 1 then
                ValueText := CopyStr(ValueText, 1, StopPosition - 1);
        end;

        exit(DelChr(ValueText, '<>', ' '));
    end;

    local procedure BuildFELQRCodeBase64(FELUUID: Text): Text
    var
        BarcodeProvider: Interface "Barcode Image Provider 2D";
        TempBlob: Codeunit "Temp Blob";
        Base64Convert: Codeunit "Base64 Convert";
        BarcodeEncodeSettings: Record "Barcode Encode Settings 2D";
        QRInStream: InStream;
        QRUrl: Text;
    begin
        if FELUUID = '' then
            exit('');

        QRUrl := 'https://report.feel.com.gt/ingfacereport/ingfacereport_documento?uuid=' + FELUUID;

        BarcodeEncodeSettings."Error Correction Level" := BarcodeEncodeSettings."Error Correction Level"::Quartile;
        BarcodeEncodeSettings."Module Size" := 5;
        BarcodeEncodeSettings."Quite Zone Width" := 2;

        BarcodeProvider := Enum::"Barcode Image Provider 2D"::Dynamics2D;
        TempBlob := BarcodeProvider.EncodeImage(QRUrl, Enum::"Barcode Symbology 2D"::"QR-Code", BarcodeEncodeSettings);
        TempBlob.CreateInStream(QRInStream);
        exit(Base64Convert.ToBase64(QRInStream));
    end;
}
